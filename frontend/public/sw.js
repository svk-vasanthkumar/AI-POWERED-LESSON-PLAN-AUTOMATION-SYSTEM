self.addEventListener('push', function (event) {
  if (event.data) {
    const data = event.data.json();
    const title = data.title || 'EduAI Alert';
    const options = {
      body: data.body || 'You have a new notification.',
      icon: data.icon || '/logo.png',
      badge: '/logo.png', 
      data: {
        url: data.url || '/'
      }
    };
    
    event.waitUntil(
      self.registration.showNotification(title, options)
    );
  }
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  const urlToOpen = new URL(event.notification.data.url, self.location.origin).href;
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (windowClients) {
      let matchingClient = null;
      for (let i = 0; i < windowClients.length; i++) {
        const windowClient = windowClients[i];
        if (windowClient.url === urlToOpen) {
          matchingClient = windowClient;
          break;
        }
      }
      
      if (matchingClient) {
        return matchingClient.focus();
      } else {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});
